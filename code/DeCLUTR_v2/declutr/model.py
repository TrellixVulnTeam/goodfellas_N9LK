from typing import Dict, Optional

import torch
from allennlp.data import TextFieldTensors, Vocabulary
from allennlp.models.model import Model
from allennlp.modules import FeedForward, Seq2VecEncoder, TextFieldEmbedder
from allennlp.modules.seq2vec_encoders import BagOfEmbeddingsEncoder
from allennlp.nn import InitializerApplicator
from allennlp.nn.util import get_text_field_mask

from declutr.common.masked_lm_utils import mask_tokens
from declutr.common.model_utils import all_gather_anchor_positive_pairs, unpack_batch
from declutr.losses import PyTorchMetricLearningLoss
from declutr.miners import PyTorchMetricLearningMiner


@Model.register("declutr")
class DeCLUTR(Model):
    """
    This `Model` implements a text encoder trained against a contrastive, self-supervised objective.
    After embedding the text into a text field, we will optionally encode the embeddings with a
    `Seq2SeqEncoder`. The resulting sequence is pooled using a `Seq2VecEncoder` and then passed to
    a `FeedFoward` layer, which projects the embeddings to a certain size.

    Registered as a `Model` with name "declutr".

    # Parameters

    vocab : `Vocabulary`
    text_field_embedder : `TextFieldEmbedder`
        Used to embed the input text into a `TextField`
    seq2vec_encoder : `Seq2VecEncoder`, optional, (default = `None`)
        Seq2Vec encoder layer. If `seq2seq_encoder` is provided, this encoder will pool its output.
        Otherwise, this encoder will operate directly on the output of the `text_field_embedder`.
        If `None`, defaults to `BagOfEmbeddingsEncoder` with `averaged=True`.
    feedforward : `FeedForward`, optional, (default = None).
        An optional feedforward layer to apply after the seq2vec_encoder.
    loss : `PyTorchMetricLearningLoss`, option (default = None).
        An optional metric learning loss function. Will be combined with the masked language
        modeling objective if
        `text_field_embedder.token_embedders["tokens"].masked_language_modeling` is True. Must be
        provided if `text_field_embedder.token_embedders["tokens"].masked_language_modeling` is
        False. See https://kevinmusgrave.github.io/pytorch-metric-learning/losses/ for a list of
        available loss functions.
    miner: `PyTorchMetricLearningMiner`, option (default = None).
        An optional mining function which will mine hard negatives from each batch before computing
        the loss. See https://kevinmusgrave.github.io/pytorch-metric-learning/miners/ for a list
        of available mining functions.
    initializer : `InitializerApplicator`, optional (default=`InitializerApplicator()`)
        If provided, will be used to initialize the model parameters.
    """

    def __init__(
            self,
            vocab: Vocabulary,
            text_field_embedder: TextFieldEmbedder,
            seq2vec_encoder: Optional[Seq2VecEncoder] = None,
            feedforward: Optional[FeedForward] = None,
            miner: Optional[PyTorchMetricLearningMiner] = None,
            loss: Optional[PyTorchMetricLearningLoss] = None,
            initializer: InitializerApplicator = InitializerApplicator(),
            **kwargs,
    ) -> None:
        
        vocab.add_token_to_namespace("0", namespace="labels")
        vocab.add_token_to_namespace("1", namespace="labels")
        super().__init__(vocab, **kwargs)
        self._text_field_embedder = text_field_embedder

        # (HACK): Prevents the user from having to specify the tokenizer / masked language modeling
        # objective. In the future it would be great to come up with something more elegant.
        token_embedder = self._text_field_embedder._token_embedders["tokens"]
        self._masked_language_modeling = token_embedder.masked_language_modeling
        if self._masked_language_modeling:
            self._tokenizer = token_embedder.tokenizer

        # Default to mean BOW pooler. This performs well and so it serves as a sensible default.
        self._seq2vec_encoder = seq2vec_encoder or BagOfEmbeddingsEncoder(
            text_field_embedder.get_output_dim(), averaged=True
        )
        self._feedforward = feedforward

        self._miner = miner
        self._loss = loss
        if self._loss is None and not self._masked_language_modeling:
            raise ValueError(
                (
                    "No loss function provided. You must provide a contrastive loss (DeCLUTR.loss)"
                    " and/or specify `masked_language_modeling=True` in the config when training."
                )
            )
        initializer(self)

    def forward(  # type: ignore
            self, anchors: TextFieldTensors, positives: TextFieldTensors=None, label:torch.LongTensor=None
    ) -> Dict[str, torch.Tensor]:

        """
        # Parameters

        tokens : TextFieldTensors
            From a `TextField`

        # Returns

        An output dictionary consisting of:

        embeddings : torch.FloatTensor
            A tensor of shape `(batch_size, self._seq2vec_encoder.get_output_dim())`, which is the
            representation for the given `tokens` output by the encoder. The encoder is composed of:
            `self._text_field_embedder`, and `self._seq2vec_encoder`, in that order.
        projections : torch.FloatTensor
            A tensor of shape `(batch_size, self._feedforward.get_output_dim())`, which is the
            non-linear projection of the learned representation for the given `anchor_tokens` output
            by the projection head. This field will only be included if `self._feedforward` is not
            `None`.
        loss : torch.FloatTensor, optional
            A scalar loss to be optimized.
        """
        output_dict: Dict[str, torch.Tensor] = {}
        print(label)
        print("****************************************8")

        # If multiple anchors were sampled, we need to unpack them.
        anchors = unpack_batch(anchors)
        # Mask anchor input ids and get labels required for MLM.
        if self.training and self._masked_language_modeling:
            anchors = mask_tokens(anchors, self._tokenizer)
        # This is the textual representation learned by a model and used for downstream tasks.
        masked_lm_loss, embedded_anchors = self._forward_internal(anchors, output_dict)
        # If positives are supplied by DataLoader and we are training, compute a contrastive loss.
        if self.training:
            output_dict["loss"] = 0
            # TODO: We should throw a ValueError if no postives provided by loss is not None.
            if self._loss is not None:
                # Like the anchors, if we sampled multiple positives, we need to unpack them.
                positives = unpack_batch(positives)
                # Positives are represented by their mean embedding a la
                # https://arxiv.org/abs/1902.09229.
                _, embedded_positives = self._forward_internal(positives)
                embedded_positive_chunks = []
                for i, chunk in enumerate(
                        torch.chunk(embedded_positives, chunks=embedded_anchors.size(0), dim=0)
                ):
                    embedded_positive_chunks.append(torch.mean(chunk, dim=0))
                embedded_positives = torch.stack(embedded_positive_chunks)
                
                # If we are training on multiple GPUs using DistributedDataParallel, then a naive
                # application would result in 2 * (batch_size/n_gpus - 1) number of negatives per
                # GPU. To avoid this, we need to gather the anchors/positives from each replica on
                # every other replica in order to generate the correct number of negatives,
                # i.e. 2 * (batch_size - 1), before computing the contrastive loss.
                embedded_anchors, embedded_positives = all_gather_anchor_positive_pairs(
                    embedded_anchors, embedded_positives
                )
                embedded_positives_1=embedded_positives[torch.nonzero(label==1).view(1,-1)[0],:]
                embedded_positives_0=embedded_positives[torch.nonzero(label==0).view(1,-1)[0],:]
                embedded_anchors_1=embedded_anchors[torch.nonzero(label==1).view(1,-1)[0],:]
                embedded_anchors_0=embedded_anchors[torch.nonzero(label==0).view(1,-1)[0],:]
                #print(embedded_positives_1.shape)
                #print(embedded_positives_0.shape)
                #print(embedded_anchors_1.shape)
                #print(embedded_anchors_0.shape)
                #embedded_anchors_0 = embedded_anchors_1 = embedded_anchors
                #embedded_positives_0 = embedded_positives_1 = embedded_positives
                # Get embeddings into the format that the PyTorch Metric Learning library expects
                # before computing the loss (with an optional mining step).
                print(embedded_positives_1.shape)
                print(embedded_anchors_1.shape)
                print("*********************************8")
                print(embedded_positives_0.shape)
                print(embedded_anchors_0.shape)

                if(embedded_positives_1.shape[0]>0 and embedded_positives_0.shape[0]>0):
                      embeddings, labels, parties = self._loss.get_embeddings_and_labels(
                                embedded_anchors_0, embedded_positives_0,embedded_anchors_1,embedded_positives_1
                         )
                      indices_tuple = self._miner(embeddings, labels) if self._miner is not None else None
                      output_dict["loss"] += self._loss(embeddings, labels, indices_tuple=indices_tuple, parties=parties)
                else:
                    output_dict["loss"]+=torch.zeros(1,device='cuda:0')
                    #masked_lm_loss = None
            # Loss may be derived from contrastive objective, MLM objective or both.
            if masked_lm_loss is not None:
                output_dict["loss"] += masked_lm_loss

        return output_dict

    def _forward_internal(
            self,
            tokens: TextFieldTensors,
            output_dict: Optional[Dict[str, torch.Tensor]] = None,
    ) -> torch.Tensor:

        masked_lm_loss, embedded_text = self._text_field_embedder(tokens)
        mask = get_text_field_mask(tokens).float()

        embedded_text = self._seq2vec_encoder(embedded_text, mask=mask)
        # Don't hold on to embeddings or projections during training.
        if output_dict is not None and not self.training:
            output_dict["embeddings"] = embedded_text.clone().detach()

        # Representations produced by a non-linear projection can be used for training with a
        # contrastive loss. Previous works in computer vision have found this projection head to
        # improve the quality of the learned embeddings (see: https://arxiv.org/abs/2002.05709).
        # When embedding text with a trained model, we want the representation produced by the
        # encoder network. We therefore call these vectors "projections" to distinguish them from
        # the "embeddings".
        if self._feedforward is not None:
            embedded_text = self._feedforward(embedded_text)
            if output_dict is not None and not self.training:
                output_dict["projections"] = embedded_text.clone().detach()

        return masked_lm_loss, embedded_text

    default_predictor = "declutr"
